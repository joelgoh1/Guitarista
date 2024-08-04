import React from 'react';
import styled from 'styled-components';

const FooterContainer = styled.footer`
  padding: 20px;
  background: #333;
  color: #fff;
  text-align: center;
`;

const FooterLinks = styled.div`
  display: flex;
  justify-content: center;
  gap: 20px;
  margin-bottom: 10px;
`;

const FooterLink = styled.a`
  color: #fff;
  text-decoration: none;
  &:hover {
    text-decoration: underline;
  }
`;

const Footer: React.FC = () => {
  return (
    <FooterContainer>
      <FooterLinks>
        <FooterLink href="#">Home</FooterLink>
        <FooterLink href="#">Lessons</FooterLink>
        <FooterLink href="#">Training</FooterLink>
        <FooterLink href="#">Tabgen</FooterLink>
        <FooterLink href="#">Achievements</FooterLink>
        <FooterLink href="#">Progress</FooterLink>
        <FooterLink href="#">Profile</FooterLink>
        <FooterLink href="#">Library</FooterLink>
        <FooterLink href="#">Game</FooterLink>
      </FooterLinks>
      <div>
        Follow us on 
        <a href="#"> Facebook</a>, 
        <a href="#"> Twitter</a>, 
        <a href="#"> Instagram</a>
      </div>
      <div>Contact: info@guitartrainer.com</div>
    </FooterContainer>
  );
};

export default Footer;
